// Fixed-seed random-stimulus testbench for uart_rx (not a gate; tools/check
// reports which plan items it hits, i.e. which are reachable by accident).
//
// Legal stimulus only, chosen at random from an in-testbench xorshift32 (not
// $urandom, whose sequence depends on the simulator version): well-formed and
// bad-stop-bit frames with random data and +/-1 clock of jitter per bit, low
// glitches of 1 clock to 2 bit times, idle gaps, rare resets, prescale 1..8
// changed only while the line is idle and the receiver is not busy, and a sink
// that is always ready, randomly ready, or stalled. No checks: exploration only.
`timescale 1ns / 1ps

module tb_rand_rx;

  localparam int CLK_PERIOD = 8;
  localparam int EVENTS = 600;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  logic [15:0] prescale = 16'd5;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         busy, overrun_error, frame_error;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart_rx #(.DATA_WIDTH(8)) dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  // One generator per process, so process ordering cannot change the stream.
  function automatic logic [31:0] xorshift(input logic [31:0] x);
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return x;
  endfunction

  logic [31:0] s_stim  = 32'h2545_F491;
  logic [31:0] s_ready = 32'h9E37_79B9;
  int unsigned r;
  logic [1:0] ready_mode = 2'd0;  // 0 always, 1 random, 2 stalled

  task automatic rnd(output int unsigned v);
    s_stim = xorshift(s_stim);
    v = s_stim;
  endtask

  // Drive on the falling edge so inputs are stable at every rising edge.
  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic hold_bit(input logic v);
    int unsigned j;
    rnd(j);
    rxd = v;
    wait_clks(int'(prescale) * 8 + int'(j % 3) - 1);
  endtask

  task automatic frame(input logic [7:0] b, input logic stop);
    hold_bit(1'b0);
    for (int i = 0; i < 8; i++) hold_bit(b[i]);
    hold_bit(stop);
    rxd = 1'b1;
  endtask

  always @(negedge clk) begin
    s_ready = xorshift(s_ready);
    case (ready_mode)
      2'd0: m_axis_tready = 1'b1;
      2'd1: m_axis_tready = s_ready[0];
      default: m_axis_tready = 1'b0;
    endcase
  end

  initial begin
    rst = 1'b1; wait_clks(4);
    rst = 1'b0; wait_clks(4);
    for (int e = 0; e < EVENTS; e++) begin
      rnd(r);
      if (r % 10 < 3) begin
        rnd(r);
        ready_mode = (r % 10 < 5) ? 2'd0 : (r % 10 < 8) ? 2'd1 : 2'd2;
      end
      rnd(r);
      if (r % 100 < 60) begin
        int unsigned d, s;
        rnd(d); rnd(s);
        frame(d[7:0], (s % 10) != 0);
      end else if (r % 100 < 75) begin
        int unsigned n;
        rnd(n);
        rxd = 1'b0;
        wait_clks(1 + int'(n % (int'(prescale) * 16)));
        rxd = 1'b1;
      end else if (r % 100 < 99) begin
        int unsigned n;
        rnd(n);
        wait_clks(int'(n % (int'(prescale) * 32)));
      end else begin
        int unsigned n;
        rnd(n);
        rst = 1'b1; wait_clks(1 + int'(n % 4));
        rst = 1'b0;
      end
      if (!busy && rxd) begin
        rnd(r);
        if (r % 10 == 0) begin
          rnd(r);
          prescale = 16'(1 + r % 8);
        end
      end
    end
    wait_clks(200);
    $finish;
  end

endmodule
