`timescale 1ns / 1ps

// rxd is held low through the first frame error and through all data bits of
// the restarted frame, but goes high half a bit before that frame's stop bit
// sample. The second frame is then received as 0x00 instead of erroring.
module tb;

  localparam int CLK_PERIOD = 8;
  localparam int P = 5;
  localparam int FRAME = 76 * P;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  logic [15:0] prescale = P;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         busy, overrun_error, frame_error;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  int fe_count = 0;
  int n_valid = 0;
  logic [7:0] got = 8'hFF;

  always @(negedge clk) begin
    if (frame_error) fe_count++;
    if (m_axis_tvalid) begin
      got = m_axis_tdata;
      n_valid++;
    end
    if (overrun_error) $fatal(1, "unexpected overrun_error");
  end

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic do_reset();
    rst = 1'b0; wait_clks(2);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(2);
  endtask

  initial begin
    int guard;
    do_reset();
    wait_clks(20);

    rxd = 1'b0;
    guard = 0;
    do begin
      @(negedge clk);
      guard++;
      if (guard > 2 * FRAME) $fatal(1, "no first frame error");
    end while (!frame_error);

    // Receiver restarts next clock; release rxd mid stop bit of that frame.
    wait_clks(1 + 72 * P);
    rxd = 1'b1;
    wait_clks(2 * FRAME);

    if (fe_count != 1) $fatal(1, "expected exactly 1 frame error, got %0d", fe_count);
    if (n_valid != 1) $fatal(1, "expected 1 received word, got %0d", n_valid);
    if (got !== 8'h00) $fatal(1, "got 0x%02h, expected 0x00", got);

    $display("NEAR-MISS done: one frame error, second frame received as 0x00");
    $finish;
  end

  initial begin
    #2ms;
    $fatal(1, "timeout");
  end

endmodule
