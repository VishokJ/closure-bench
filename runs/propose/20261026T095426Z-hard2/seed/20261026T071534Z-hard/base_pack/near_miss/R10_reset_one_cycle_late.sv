`timescale 1ns / 1ps
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  logic [15:0] prescale = 16'd2;
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

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  int bit_clks;
  bit found;
  logic [7:0] b;

  initial begin
    @(negedge clk);
    rst = 1'b1; wait_clks(3);
    rst = 1'b0; wait_clks(5);
    bit_clks = int'(prescale) * 8;
    b = 8'hA5;
    rxd = 1'b0; wait_clks(bit_clks);
    for (int i = 0; i < 8; i++) begin
      rxd = b[i]; wait_clks(bit_clks);
    end
    rxd = 1'b0;
    found = 0;
    for (int n = 0; n < 4 * bit_clks && !found; n++) begin
      @(negedge clk);
      if (frame_error) found = 1;
    end
    if (!found) $fatal(1, "frame_error never pulsed");
    if (rst !== 1'b0) $fatal(1, "rst unexpectedly high on pulse cycle");
    // Miss: reset one cycle after the pulse
    @(negedge clk);
    if (frame_error !== 1'b0) $fatal(1, "frame_error pulse longer than one cycle");
    rst = 1'b1;
    @(negedge clk);
    if (frame_error !== 1'b0) $fatal(1, "frame_error high during reset");
    @(negedge clk);
    if (frame_error !== 1'b0) $fatal(1, "frame_error high during reset");
    rxd = 1'b1;
    wait_clks(2);
    rst = 1'b0;
    wait_clks(10);
    if (frame_error !== 1'b0) $fatal(1, "frame_error high after reset");
    $display("NEAR MISS done");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
