`timescale 1ns / 1ps
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  logic [15:0] prescale = 16'd5;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  int n_valid = 0;
  int n_fe = 0;
  logic [7:0] last_data = 8'h00;

  always @(posedge clk) begin
    if (m_axis_tvalid && m_axis_tready) begin
      n_valid = n_valid + 1;
      last_data = m_axis_tdata;
    end
    if (frame_error) n_fe = n_fe + 1;
  end

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  bit seen_busy;

  initial begin
    wait_clks(2);
    rst = 1'b1; wait_clks(3);
    rst = 1'b0; wait_clks(10);

    // Low pulse of 22 clocks: still low at the mid-start-bit sample, so the
    // start bit is accepted (no false-start rejection). Line then stays high:
    // data bits all 1 and a valid stop bit -> word 0xFF.
    seen_busy = 0;
    rxd = 1'b0;
    repeat (22) begin
      @(negedge clk);
      if (busy) seen_busy = 1;
    end
    rxd = 1'b1;
    if (!seen_busy) $fatal(1, "receiver never started");

    wait_clks(600);
    if (n_valid != 1) $fatal(1, "expected start to be accepted (1 word), got %0d", n_valid);
    if (last_data !== 8'hFF) $fatal(1, "got 0x%02h, expected 0xFF", last_data);
    if (n_fe != 0) $fatal(1, "unexpected frame error");
    if (busy) $fatal(1, "receiver still busy");

    $display("near miss done: start bit accepted");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
